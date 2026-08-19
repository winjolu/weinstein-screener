"""Separating real explosions from unapplied splits.

The test that matters is the one where the detector must NOT fire. A
filter that catches every defect and also deletes the best trade in the
database is worse than no filter, because the losses it causes are
invisible while the defects it catches are advertised.
"""
import unittest

from market_core import jumps


def _series(closes, volumes=None):
    volumes = volumes or [10_000] * len(closes)
    return [{"time": f"2024-01-{i+1:02d}", "close": c, "volume": v}
            for i, (c, v) in enumerate(zip(closes, volumes))]


class ClassificationTest(unittest.TestCase):
    def test_a_jump_on_huge_volume_is_a_real_move(self):
        # The APLD shape: price nearly doubles on 40x normal volume.
        closes = [8.0] * 20 + [30.0]
        volumes = [5_000] * 20 + [200_000]
        found = jumps.scan_series(_series(closes, volumes))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["verdict"], jumps.REAL)

    def test_a_jump_on_ordinary_volume_is_suspect(self):
        # A restatement into different units moves the price and leaves
        # the share count alone.
        closes = [8.0] * 20 + [160.0]
        volumes = [5_000] * 21
        found = jumps.scan_series(_series(closes, volumes))
        self.assertEqual(found[0]["verdict"], jumps.SUSPECT)

    def test_a_collapse_on_ordinary_volume_is_suspect(self):
        closes = [160.0] * 20 + [8.0]
        found = jumps.scan_series(_series(closes))
        self.assertEqual(found[0]["verdict"], jumps.SUSPECT)

    def test_an_ordinary_series_produces_nothing(self):
        found = jumps.scan_series(_series([10.0, 10.4, 10.1, 10.8, 11.2]))
        self.assertEqual(found, [])

    def test_sub_dollar_noise_is_ignored(self):
        # 0.004 to 0.15 is a 37x "jump" and is entirely rounding.
        found = jumps.scan_series(_series([0.004] * 20 + [0.15]))
        self.assertEqual(found, [])

    def test_no_volume_history_is_treated_as_suspect_not_real(self):
        # Absence of evidence must not read as confirmation, or every
        # defect in a thin name gets waved through.
        bars = [{"time": f"2024-01-{i+1:02d}", "close": 8.0, "volume": 0}
                for i in range(20)]
        bars.append({"time": "2024-01-21", "close": 160.0, "volume": 0})
        self.assertEqual(jumps.scan_series(bars)[0]["verdict"], jumps.SUSPECT)

    def test_the_volume_multiple_is_reported_for_judgement(self):
        closes = [8.0] * 20 + [30.0]
        volumes = [5_000] * 20 + [200_000]
        found = jumps.scan_series(_series(closes, volumes))
        self.assertAlmostEqual(found[0]["volume_multiple"], 40.0, places=6)

    def test_a_nonsense_threshold_raises(self):
        with self.assertRaises(ValueError):
            jumps.scan_series(_series([1.0, 2.0]), ratio_threshold=1.0)


class WindowTest(unittest.TestCase):
    def test_only_suspect_dates_are_returned(self):
        # A real move is not a reason to exclude a window. APLD's genuine
        # 130-bagger straddles its own jump and must survive.
        closes = [8.0] * 20 + [30.0] + [31.0] * 5 + [200.0]
        volumes = [5_000] * 20 + [200_000] + [5_000] * 6
        dates = jumps.suspect_windows(_series(closes, volumes))
        self.assertEqual(len(dates), 1)
        self.assertNotIn("2024-01-21", dates)


class PriceScaleTest(unittest.TestCase):
    def test_a_normal_price_is_plausible(self):
        self.assertTrue(jumps.price_scale_is_plausible(_series([40.0] * 30)))

    def test_a_six_figure_share_price_is_not(self):
        # ATXG recorded at 98,481 a share. Returns survive it; dollar
        # volume does not.
        self.assertFalse(jumps.price_scale_is_plausible(_series([98_481.0] * 30)))

    def test_an_empty_series_is_not_assumed_plausible(self):
        self.assertFalse(jumps.price_scale_is_plausible([]))

    def test_a_corrupt_past_is_not_excused_by_a_normal_present(self):
        # ATXG's recent median is $5.75 and its history contains $98,481.
        # Sampling only the tail reported it clean, which is a check
        # answering about data it never examined.
        bars = _series([98_481.0] * 30 + [5.75] * 250)
        self.assertFalse(jumps.price_scale_is_plausible(bars))


class ActionProximityTest(unittest.TestCase):
    def test_a_nearby_action_is_found(self):
        self.assertTrue(jumps.actions_near(["2016-11-14"], "2016-11-16"))

    def test_a_distant_action_is_not(self):
        # SLS jumped on 2016-06-29 with its nearest recorded split five
        # months later, so the actions table cannot explain it either.
        self.assertFalse(jumps.actions_near(["2016-11-14"], "2016-06-29"))

    def test_unparseable_dates_do_not_raise(self):
        self.assertFalse(jumps.actions_near(["", "not-a-date"], "2016-06-29"))

    def test_no_actions_at_all_is_false_not_true(self):
        self.assertFalse(jumps.actions_near([], "2016-06-29"))
