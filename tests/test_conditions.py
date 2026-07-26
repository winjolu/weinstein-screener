"""Condition-logic regressions.

The swing-rule case here is the highest-value test in the suite: it
caught a real bug during development. My first implementation measured
the decline to the base's low instead of the decline's own low and
returned 36.25 where the book's worked example states 37.75. Nothing
about that output looked wrong on inspection — it was a plausible
number in the right range, and only checking it against a stated answer
exposed it.
"""
import unittest

from screener import conditions as C
from tests.synthetic import bar, weekly_dates


def _series(segments):
    """Builds (highs, lows, closes) from (high, low, close, repeat) tuples."""
    highs, lows, closes = [], [], []
    for high, low, close, count in segments:
        for _ in range(count):
            highs.append(high)
            lows.append(low)
            closes.append(close)
    return highs, lows, closes


class SwingRuleTest(unittest.TestCase):
    """Peak before the decline, minus the low that followed, added back
    onto that peak — checked against the book's own worked figures.
    """

    def setUp(self):
        self.peak, self.decline_low, self.resistance = 27.625, 17.5, 25.0
        self.highs, self.lows, self.closes = _series([
            (20.0, 19.0, 19.5, 10),                       # quiet lead-in
            (self.peak, 26.0, 27.0, 6),                   # the peak (point A)
            (22.0, self.decline_low, 18.0, 8),            # the decline (point B)
            (self.resistance, 19.0, 22.0, 26),            # the base, capped at resistance
            (29.5, 27.5, 29.0, 1),                        # breakout above the old peak
            (30.0, 28.0, 29.5, 4),
        ])
        self.base = C._find_base_and_breakout(self.closes, self.highs, self.lows)

    def test_reproduces_book_target(self):
        target, _, _, detail = C._evaluate_risk_reward(
            self.highs, self.lows, self.closes, self.base["resistance_level"],
            self.base["breakout_idx"], self.base["base_start"], self.base["base_end"],
        )
        self.assertEqual(detail["target_method"], "swing_rule")
        self.assertAlmostEqual(detail["prior_peak"], self.peak, places=6)
        self.assertAlmostEqual(detail["decline_low"], self.decline_low, places=6)
        self.assertAlmostEqual(target, 37.75, places=6)

    def test_measures_decline_low_not_base_low(self):
        """The specific bug: the decline's low sits before the base and so
        falls outside the base window. Measuring the base's low instead
        understates the move.
        """
        _, _, _, detail = C._evaluate_risk_reward(
            self.highs, self.lows, self.closes, self.base["resistance_level"],
            self.base["breakout_idx"], self.base["base_start"], self.base["base_end"],
        )
        self.assertLess(detail["decline_low"], detail["base_low"])


class SwingRuleApplicabilityTest(unittest.TestCase):
    def test_falls_back_when_base_sits_above_prior_peak(self):
        """The rule's geometry is peak -> decline -> base -> reclaim. When
        the base's own high already exceeds the prior peak there was no
        decline to reclaim, and projecting from a peak the stock left
        behind produces targets under the current price.
        """
        highs, lows, closes = _series([
            (20.0, 18.0, 19.0, 20),      # low prior peak
            (60.0, 55.0, 58.0, 26),      # base far above it
            (65.0, 62.0, 64.0, 5),       # breakout
        ])
        base = C._find_base_and_breakout(closes, highs, lows)
        target, _, _, detail = C._evaluate_risk_reward(
            highs, lows, closes, base["resistance_level"],
            base["breakout_idx"], base["base_start"], base["base_end"],
        )
        self.assertNotEqual(detail["target_method"], "swing_rule")
        self.assertGreater(target, closes[base["breakout_idx"]])


class BaseDetectionTest(unittest.TestCase):
    def test_finds_transition_not_latest_high(self):
        """In a sustained advance every bar clears the prior window, so the
        meaningful bar is the first of the run, not the most recent.
        """
        highs, lows, closes = _series([
            (20.0, 18.0, 19.0, 30),      # flat base
            (21.0, 19.0, 20.5, 1),       # the breakout
        ])
        for step in range(1, 11):        # then keeps making new highs
            highs.append(21.0 + step)
            lows.append(19.0 + step)
            closes.append(20.5 + step)
        base = C._find_base_and_breakout(closes, highs, lows)
        self.assertEqual(base["breakout_idx"], 30)
        self.assertEqual(base["breakout_age_weeks"], len(closes) - 1 - 30)

    def test_returns_empty_without_enough_history(self):
        highs, lows, closes = _series([(10.0, 9.0, 9.5, 5)])
        base = C._find_base_and_breakout(closes, highs, lows)
        self.assertIsNone(base["breakout_idx"])
        self.assertIsNone(base["resistance_level"])


class ScoringTest(unittest.TestCase):
    """The C3 fix: unknown must not be scored as failed."""

    def _conds(self, **overrides):
        base = {
            "stage_setup": True, "price_above_ma": True, "volume_confirmation": True,
            "rs_improving": True, "sector_strength": True, "market_stage": True,
            "resistance_breakout": True, "pullback_quality": True, "risk_reward": True,
        }
        base.update(overrides)
        return base

    def test_unknown_is_not_a_failure(self):
        unknowns = self._conds(resistance_breakout=None, pullback_quality=None)
        failures = self._conds(resistance_breakout=False, pullback_quality=False)
        self.assertGreater(
            C.score_conditions(unknowns)["score"],
            C.score_conditions(failures)["score"],
        )

    def test_full_information_matches_legacy_eight_of_nine(self):
        """With everything resolved the new model must still demand 8."""
        seven = C.score_conditions(self._conds(risk_reward=False, pullback_quality=False))
        eight = C.score_conditions(self._conds(risk_reward=False))
        self.assertFalse(seven["actionable"])
        self.assertTrue(eight["actionable"])
        self.assertEqual(eight["required"], 8)

    # Spelled out rather than read from the constant under test. Iterating
    # NON_NEGOTIABLE_CONDITIONS meant emptying it made this pass vacuously,
    # which a mutation check caught on the suite's first run.
    EXPECTED_GATES = ("stage_setup", "price_above_ma", "market_stage")

    def test_hard_gates_are_the_expected_three(self):
        self.assertEqual(set(C.NON_NEGOTIABLE_CONDITIONS), set(self.EXPECTED_GATES))

    def test_hard_gate_blocks_regardless_of_score(self):
        for gate in self.EXPECTED_GATES:
            result = C.score_conditions(self._conds(**{gate: False}))
            self.assertFalse(result["actionable"], gate)
            self.assertIn(gate, result["blocking"])

    def test_evidence_floor_blocks_thin_information(self):
        thin = self._conds(
            volume_confirmation=None, resistance_breakout=None,
            pullback_quality=None, risk_reward=None,
        )
        result = C.score_conditions(thin)
        self.assertEqual(result["resolved"], 5)
        self.assertFalse(result["actionable"])
        self.assertIn("resolved", result["reason"])

    def test_counts_partition_cleanly(self):
        result = C.score_conditions(self._conds(risk_reward=False, pullback_quality=None))
        self.assertEqual(result["met"] + result["failed"] + result["unknown"], 9)
        self.assertEqual(result["resolved"], result["met"] + result["failed"])


class StopPlacementTest(unittest.TestCase):
    def test_stop_sits_below_entry_and_is_reported_as_a_percentage(self):
        highs, lows, closes = _series([
            (20.0, 18.0, 19.0, 30),
            (21.0, 19.5, 20.5, 1),
            (22.0, 20.0, 21.5, 3),
        ])
        base = C._find_base_and_breakout(closes, highs, lows)
        _, stop, _, detail = C._evaluate_risk_reward(
            highs, lows, closes, base["resistance_level"],
            base["breakout_idx"], base["base_start"], base["base_end"],
        )
        entry = closes[base["breakout_idx"]]
        self.assertLess(stop, entry)
        self.assertAlmostEqual(detail["stop_pct"], (entry - stop) / entry * 100, places=6)


if __name__ == "__main__":
    unittest.main()
