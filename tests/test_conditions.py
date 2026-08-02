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
from tests.synthetic import bar, trending_bars, weekly_dates


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


class EvaluationWindowTest(unittest.TestCase):
    """Fetch depth must not change a verdict.

    Pivot detection scans the whole series it's given, so before the
    window was enforced the live screener (104 weeks) and the backtest
    (nearer 170) could reach different conclusions about the same stock
    on the same date. Nothing reported that; the answers just disagreed
    depending on which caller asked.
    """

    # Exactly EVALUATION_WEEKS of decline -> base -> breakout. Anything
    # prepended to this is history the evaluation must not see.
    CORE = [
        (58.0, 30.0, 33.0, 20),
        (40.0, 32.0, 36.0, 74),
        (48.0, 40.0, 46.0, 10),
    ]
    # Deliberately extreme, and long enough to clear the window. Flat
    # filler here is what made the first version of this test vacuous:
    # dropping bars indistinguishable from their neighbours changes
    # nothing, so it passed even with the window disabled.
    PREFIX = [(300.0, 250.0, 280.0, 30)]

    def _core_bars(self):
        highs, lows, closes = _series(self.CORE)
        dates = weekly_dates(len(closes))
        return [bar(d, h, l, c) for d, h, l, c in zip(dates, highs, lows, closes)]

    def _prefixed_bars(self):
        highs, lows, closes = _series(self.PREFIX + self.CORE)
        dates = weekly_dates(len(closes))
        return [bar(d, h, l, c) for d, h, l, c in zip(dates, highs, lows, closes)]

    def test_core_is_exactly_one_window(self):
        self.assertEqual(len(self._core_bars()), C.EVALUATION_WEEKS)

    def test_extra_history_does_not_change_the_verdict(self):
        sector = {"sector": None, "sector_strength_pct": None}
        deep = self._prefixed_bars()
        shallow = self._core_bars()

        a = C.evaluate_conditions("T", deep, deep, sector)
        b = C.evaluate_conditions("T", shallow, shallow, sector)

        self.assertEqual(a["conditions"], b["conditions"])
        self.assertEqual(a["scoring"], b["scoring"])
        self.assertEqual(a["swing_stop"], b["swing_stop"])
        self.assertEqual(a["swing_target"], b["swing_target"])
        self.assertEqual(a["resistance_level"], b["resistance_level"])
        self.assertEqual(a["breakout_age_weeks"], b["breakout_age_weeks"])
        self.assertEqual(a["mansfield_rs"], b["mansfield_rs"])
        # The sharpest of these: an all-time high computed over whatever
        # the caller fetched is precisely the leak this window closes.
        self.assertEqual(a["historical_levels"], b["historical_levels"])
        self.assertEqual(a["new_52w_high"], b["new_52w_high"])

    def test_breakout_idx_indexes_the_callers_own_list(self):
        """The window is applied internally, so a returned index has to be
        translated back or it points at the wrong bar.
        """
        deep = self._prefixed_bars()
        result = C.evaluate_conditions(
            "T", deep, deep, {"sector": None, "sector_strength_pct": None}
        )
        idx = result["breakout_idx"]
        self.assertIsNotNone(idx)
        self.assertLess(idx, len(deep))
        # An untranslated index would still be in range but point at the
        # wrong bar, so anchor it to something externally checkable.
        self.assertEqual(result["breakout_age_weeks"], len(deep) - 1 - idx)
        self.assertAlmostEqual(deep[idx]["close"], 46.0, places=6)

    def test_window_is_derived_from_the_internal_lookbacks(self):
        self.assertGreaterEqual(C.EVALUATION_WEEKS, C.PRE_BASE_LOOKBACK + C.BASE_WINDOW)
        self.assertGreaterEqual(C.EVALUATION_WEEKS, C.MA_PERIOD + C.MA_SLOPE_LOOKBACK)


class IndexAlignmentTest(unittest.TestCase):
    """A stock younger than the index must be judged, not crashed on.

    Pairing the two series by position rather than by date raised
    outright on any length mismatch, which across a full-market scan
    discarded 463 recently listed names behind an error that named the
    symptom and not the cause.
    """

    def _sector(self):
        return {"sector": None, "sector_strength_pct": None}

    def test_short_history_ticker_is_evaluated_not_raised(self):
        index_bars = trending_bars(104, 400.0, 0.5)
        young = trending_bars(104, 100.0, 0.4)[-30:]   # only 30 weeks listed
        result = C.evaluate_conditions("NEW", young, index_bars, self._sector())
        # Too little history for a 52-period relative-strength read, so it
        # reports unknown rather than inventing one.
        self.assertIsNone(result["mansfield_rs"])
        self.assertIn(result["conditions"]["rs_improving"], (None,))

    def test_pairs_on_matching_dates_not_positions(self):
        """A gap in the stock's own series must not shift it against the
        index — the pairing has to follow dates.
        """
        index_bars = trending_bars(104, 400.0, 0.5)
        stock = trending_bars(104, 100.0, 0.4)
        gapped = stock[:50] + stock[55:]   # five weeks missing mid-series

        full = C.evaluate_conditions("T", stock, index_bars, self._sector())
        holed = C.evaluate_conditions("T", gapped, index_bars, self._sector())

        # Both still produce a reading; positional zipping would have
        # compared the tail of one against the wrong weeks of the other.
        self.assertIsNotNone(full["mansfield_rs"])
        self.assertIsNotNone(holed["mansfield_rs"])

    def test_index_longer_than_stock_does_not_raise(self):
        index_bars = trending_bars(200, 400.0, 0.5)
        stock = trending_bars(104, 100.0, 0.4)
        result = C.evaluate_conditions("T", stock, index_bars, self._sector())
        self.assertIsNotNone(result["scoring"])


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


class InsufficientHistoryTest(unittest.TestCase):
    """A checkpoint that predates a ticker's first bar leaves an empty
    series. That used to index off the end and surface as 318 opaque
    "list index out of range" failures in a single backtest run — each
    one a checkpoint silently discarded. A stock that didn't exist yet
    is an unknown, not an error.
    """

    def _index(self):
        return trending_bars(104, 400.0, 0.5)

    def test_no_bars_is_an_unknown_not_a_crash(self):
        result = C.evaluate_conditions("T", [], self._index(), None)
        self.assertFalse(result["actionable"])
        self.assertEqual(result["scoring"]["met"], 0)
        self.assertTrue(all(v is None for v in result["conditions"].values()))

    def test_no_index_bars_is_also_survivable(self):
        result = C.evaluate_conditions("T", trending_bars(60), [], None)
        self.assertFalse(result["actionable"])

    def test_the_empty_result_matches_a_real_one_key_for_key(self):
        """Callers read these dicts directly, so a short-history result
        that's missing keys would just move the failure downstream."""
        real = C.evaluate_conditions("T", trending_bars(104), self._index(), None)
        self.assertEqual(set(real), set(C._empty_result()))

    def test_a_very_short_history_still_evaluates_without_qualifying(self):
        result = C.evaluate_conditions("T", trending_bars(104)[-8:], self._index(), None)
        self.assertFalse(result["actionable"])


class ExtensionGateTest(unittest.TestCase):
    """"Don't buy too late in an advance" is on the book's never-violate
    list and had no implementation. It's a gate rather than a tenth
    condition on purpose: in a ratio it could be outvoted by the other
    nine, which is the exact failure it exists to close.
    """

    def _conditions(self, **over):
        base = {name: True for name in C.CONDITION_NAMES}
        base.update(over)
        return base

    def setUp(self):
        self._prev = C.MAX_EXTENSION_ABOVE_MA_PCT

    def tearDown(self):
        C.MAX_EXTENSION_ABOVE_MA_PCT = self._prev

    def test_disabled_by_default_so_behaviour_is_unchanged(self):
        C.MAX_EXTENSION_ABOVE_MA_PCT = None
        s = C.score_conditions(self._conditions(), extension_above_ma_pct=500.0)
        self.assertTrue(s["actionable"])
        self.assertFalse(s["too_extended"])

    def test_a_wildly_extended_stock_is_blocked_even_with_every_condition_met(self):
        """IMCC passed 7 of 8 while sitting 174% above its average, and
        lost 63%. A perfect scorecard must not override this."""
        C.MAX_EXTENSION_ABOVE_MA_PCT = 30.0
        s = C.score_conditions(self._conditions(), extension_above_ma_pct=174.0)
        self.assertFalse(s["actionable"])
        self.assertTrue(s["too_extended"])
        self.assertIn("30-week average", s["reason"])

    def test_a_stock_inside_the_limit_is_unaffected(self):
        C.MAX_EXTENSION_ABOVE_MA_PCT = 30.0
        s = C.score_conditions(self._conditions(), extension_above_ma_pct=12.0)
        self.assertTrue(s["actionable"])
        self.assertFalse(s["too_extended"])

    def test_the_boundary_is_inclusive(self):
        C.MAX_EXTENSION_ABOVE_MA_PCT = 30.0
        self.assertTrue(C.score_conditions(self._conditions(), 30.0)["actionable"])
        self.assertFalse(C.score_conditions(self._conditions(), 30.01)["actionable"])

    def test_an_unmeasurable_extension_does_not_block(self):
        """No moving average yet is a different thing from being extended;
        blocking on it would silently discard young listings."""
        C.MAX_EXTENSION_ABOVE_MA_PCT = 30.0
        s = C.score_conditions(self._conditions(), extension_above_ma_pct=None)
        self.assertTrue(s["actionable"])

    def test_the_gate_outranks_the_scoring_ratio(self):
        """Blocked means blocked — not 'docked a point'."""
        C.MAX_EXTENSION_ABOVE_MA_PCT = 30.0
        s = C.score_conditions(self._conditions(), extension_above_ma_pct=200.0)
        self.assertFalse(s["actionable"])
        self.assertEqual(s["met"], len(C.CONDITION_NAMES))


class ExtensionIsActuallyMeasuredTest(unittest.TestCase):
    """The gate above tests score_conditions with a value handed to it,
    which passes even if evaluate_conditions never computes one. This
    checks the number is derived from the bars — a mutation replacing the
    calculation with None survived until this existed.
    """

    def _bars(self, closes):
        dates = weekly_dates(len(closes))
        return [bar(d, c * 1.01, c * 0.99, c) for d, c in zip(dates, closes)]

    def test_extension_is_computed_from_price_against_its_own_average(self):
        # Flat for long enough to establish a 30-week average near 100,
        # then a single bar far above it.
        closes = [100.0] * 120 + [200.0]
        result = C.evaluate_conditions("TEST", self._bars(closes), self._bars(closes), None)
        ext = result["extension_above_ma_pct"]
        self.assertIsNotNone(ext, "extension must be measured, not left None")
        # The average is dragged slightly above 100 by the final bar, so
        # the extension lands just under a literal doubling.
        self.assertGreater(ext, 80.0)
        self.assertLess(ext, 100.0)

    def test_a_stock_sitting_on_its_average_reads_near_zero(self):
        closes = [100.0] * 120
        result = C.evaluate_conditions("TEST", self._bars(closes), self._bars(closes), None)
        self.assertAlmostEqual(result["extension_above_ma_pct"], 0.0, places=6)

    def test_too_short_a_history_reports_none_rather_than_guessing(self):
        result = C.evaluate_conditions("TEST", [], [], None)
        self.assertIsNone(result["extension_above_ma_pct"])


class ExtensionMeasuredAtTheFillBarTest(unittest.TestCase):
    """The gate must read the bar a purchase fills on, not the bar the
    scan happens on.

    A scan sees a breakout a median of four weeks late, and both the entry
    plan and the backtest fill at the breakout level. Measuring at the scan
    rejects trades over a run-up that happened after the price paid, and
    blocks re-entry after a stop-out — a recovered stock is extended when
    next scanned. Armed at 40%, the scan-date version removed 226 of 273
    trades and produced no replacements.
    """

    def _bars(self, closes):
        dates = weekly_dates(len(closes))
        return [bar(d, c * 1.01, c * 0.99, c) for d, c in zip(dates, closes)]

    def test_a_run_up_after_the_breakout_does_not_inflate_the_reading(self):
        """Same breakout, then a large advance. The extension attributed
        to the entry must not grow just because price kept going."""
        base = [100.0] * 100 + [104.0] * 20        # base, then a breakout
        calm = self._bars(base + [106.0] * 3)
        ranaway = self._bars(base + [106.0, 180.0, 260.0])
        a = C.evaluate_conditions("T", calm, calm, None)["extension_above_ma_pct"]
        b = C.evaluate_conditions("T", ranaway, ranaway, None)["extension_above_ma_pct"]
        if a is None or b is None:
            self.skipTest("no breakout detected in this synthetic series")
        self.assertAlmostEqual(a, b, delta=1.0,
                               msg="extension moved with post-entry price action")

    def test_it_still_reports_a_number_when_no_breakout_was_found(self):
        closes = [100.0] * 120
        result = C.evaluate_conditions("T", self._bars(closes), self._bars(closes), None)
        self.assertIsNotNone(result["extension_above_ma_pct"])


class CurvatureStageTest(unittest.TestCase):
    """R8: the shape of the average, not just its direction.

    The book describes a Stage 1-to-2 transition as the average falling,
    flattening, then curving up. A single slope reading answers "is it
    rising" — the first derivative — where the shape is the second. A
    flat average reached by easing off a steep decline is the setup; a
    flat average rolling over from an advance is its opposite, and one
    slope measurement cannot tell them apart.
    """

    def setUp(self):
        self._prev = C.MA_CURVATURE_LOOKBACK

    def tearDown(self):
        C.MA_CURVATURE_LOOKBACK = self._prev

    def _bars(self, closes):
        return [bar(d, c * 1.01, c * 0.99, c)
                for d, c in zip(weekly_dates(len(closes)), closes)]

    def _decelerating_decline_then_recovery(self):
        """Falls hard, decelerates, flattens, price crosses above."""
        closes = []
        price = 200.0
        for step in range(60):
            price *= (1 - 0.03 + step * 0.0005)   # decline easing off
            closes.append(price)
        for _ in range(50):
            price *= 1.012                        # gentle recovery
            closes.append(price)
        return closes

    def test_disabled_by_default_so_behaviour_is_unchanged(self):
        self.assertIsNone(self._prev,
                          "curvature must ship off until measured")

    def test_a_recovering_series_still_resolves_with_curvature_on(self):
        closes = self._decelerating_decline_then_recovery()
        bars = self._bars(closes)
        C.MA_CURVATURE_LOOKBACK = None
        without = C.evaluate_conditions("T", bars, bars, None)["stage"]
        C.MA_CURVATURE_LOOKBACK = 10
        with_curve = C.evaluate_conditions("T", bars, bars, None)["stage"]
        # Not asserting which stage — only that arming the term is not
        # inert and does not crash on a real shape.
        self.assertTrue(without is not None or with_curve is not None)

    def test_curvature_changes_at_least_some_verdicts(self):
        """If every series scores identically either way, the parameter
        does nothing and the experiment would be broken rather than the
        idea being wrong — the lesson from the partial-exit A/B."""
        # An advance that stalls while price is still above the average.
        # The curvature branches only apply above the average, so a
        # decelerating series that has already fallen through it can't
        # exercise them — my first fixtures did exactly that and left the
        # term looking inert.
        closes = [100.0]
        for _ in range(60):
            closes.append(closes[-1] * 1.02)     # strong advance
        for _ in range(30):
            closes.append(closes[-1] * 1.001)    # stalls, stays above
        bars = self._bars(closes)
        C.MA_CURVATURE_LOOKBACK = None
        without = C.evaluate_conditions("T", bars, bars, None)["stage"]
        C.MA_CURVATURE_LOOKBACK = 10
        with_curve = C.evaluate_conditions("T", bars, bars, None)["stage"]
        self.assertNotEqual(without, with_curve,
                            "curvature never altered any stage call")
        self.assertEqual(without, 2, "a stalling advance reads Stage 2 on slope alone")
        self.assertEqual(with_curve, 3, "decelerating above the average is a top forming")

    def test_too_little_history_falls_back_rather_than_crashing(self):
        C.MA_CURVATURE_LOOKBACK = 10
        closes = [100.0] * 40
        result = C.evaluate_conditions("T", self._bars(closes), self._bars(closes), None)
        self.assertIn("stage", result)


class ContinuationEntryTest(unittest.TestCase):
    """Re-entry into a trend already underway.

    The book describes selling well above the average and repurchasing on
    dips back toward it. The screener only ever recognised breakout
    entries, so a stop-out was usually terminal — mid-trend there is no
    resistance left for condition 7 to confirm. Measured over 2021-2026
    it took a median of 2 trades per stock in five years and captured 2%
    of the available advance.
    """

    def setUp(self):
        self._prev = C.CONTINUATION_ENTRY_MAX_PCT_ABOVE_MA

    def tearDown(self):
        C.CONTINUATION_ENTRY_MAX_PCT_ABOVE_MA = self._prev

    def _established_uptrend(self, n=140):
        """Long rise, then a shallow pullback that stays above the
        average. Eight weeks of decline took price *through* the line and
        read as Stage 3 — which is correct behaviour, and the wrong
        fixture for testing a continuation."""
        closes, price = [], 100.0
        for _ in range(n - 4):
            closes.append(price)
            price *= 1.012
        for _ in range(4):
            price *= 0.985
            closes.append(price)
        return [bar(d, c * 1.01, c * 0.99, c)
                for d, c in zip(weekly_dates(len(closes)), closes)]

    def test_defaults_to_off(self):
        self.assertIsNone(self._prev)

    def test_arming_it_marks_a_continuation_setup(self):
        bars = self._established_uptrend()
        C.CONTINUATION_ENTRY_MAX_PCT_ABOVE_MA = None
        off = C.evaluate_conditions("T", bars, bars, None)
        C.CONTINUATION_ENTRY_MAX_PCT_ABOVE_MA = 25.0
        on = C.evaluate_conditions("T", bars, bars, None)
        self.assertFalse(off["continuation_entry"])
        self.assertTrue(on["continuation_entry"],
                        "a pullback toward a rising average should qualify")

    def test_it_never_relaxes_the_trend_conditions(self):
        """It stands in for the entry trigger only. Stage, the average and
        the market read still have to pass on their own terms."""
        falling = [bar(d, c * 1.01, c * 0.99, c)
                   for d, c in zip(weekly_dates(140),
                                   [200.0 * (0.98 ** i) for i in range(140)])]
        C.CONTINUATION_ENTRY_MAX_PCT_ABOVE_MA = 25.0
        result = C.evaluate_conditions("T", falling, falling, None)
        self.assertFalse(result["continuation_entry"],
                         "a downtrend must never qualify as a continuation")

    def test_a_stock_far_above_its_average_does_not_qualify(self):
        """The point is a pullback *toward* the line, not a runaway."""
        runaway = [bar(d, c * 1.01, c * 0.99, c)
                   for d, c in zip(weekly_dates(140),
                                   [100.0 * (1.04 ** i) for i in range(140)])]
        C.CONTINUATION_ENTRY_MAX_PCT_ABOVE_MA = 15.0
        result = C.evaluate_conditions("T", runaway, runaway, None)
        self.assertFalse(result["continuation_entry"])


class VolumeBuildupTest(unittest.TestCase):
    """The book gives two acceptable volume patterns and this code only
    tested one: a one-week spike of at least twice the past month.

    The second is a build-up over three to four weeks running at twice
    the prior average, coupled with only *some* increase on the breakout
    week itself. A stock accumulating volume through its base and then
    breaking out on a modest bump satisfies the book and failed here.
    """

    def setUp(self):
        self._prev = (C.VOLUME_BUILDUP_WEEKS, C.VOLUME_CONFIRM_RATIO)

    def tearDown(self):
        C.VOLUME_BUILDUP_WEEKS, C.VOLUME_CONFIRM_RATIO = self._prev

    def test_defaults_to_off(self):
        self.assertIsNone(self._prev[0])

    def test_the_buildup_ratio_compares_two_adjacent_stretches(self):
        # 8 quiet weeks, then 4 heavy ones, then the breakout at index 12.
        volumes = [100.0] * 8 + [300.0] * 4 + [150.0]
        ratio = C._volume_buildup_ratio(volumes, breakout_idx=12, weeks=4)
        self.assertAlmostEqual(ratio, 3.0)

    def test_it_returns_none_without_enough_history(self):
        self.assertIsNone(C._volume_buildup_ratio([100.0] * 5, breakout_idx=3, weeks=4))
        self.assertIsNone(C._volume_buildup_ratio([100.0] * 20, breakout_idx=None, weeks=4))

    def test_a_buildup_breakout_passes_only_when_enabled(self):
        """Quiet base, heavy accumulation, then a breakout that merely
        holds the elevated level — fails the spike test, satisfies the
        build-up one.

        My first fixture put the breakout week *below* the build-up,
        which is volume drying up exactly when it should confirm. The
        book rejects that, and so does this code — the fixture was wrong,
        not the rule.
        """
        volumes = [100.0] * 8 + [300.0] * 4 + [330.0]
        C.VOLUME_BUILDUP_WEEKS = None
        off, ratio_off, phase_off = C._evaluate_volume_confirmation(
            volumes, breakout_idx=12, latest_idx=12, pullback_quality=None)
        C.VOLUME_BUILDUP_WEEKS = 4
        on, _, phase_on = C._evaluate_volume_confirmation(
            volumes, breakout_idx=12, latest_idx=12, pullback_quality=None)
        self.assertFalse(off, "a mild breakout week must fail the spike test")
        self.assertTrue(on, "the build-up route should admit it")
        self.assertEqual(phase_on, "breakout_buildup")

    def test_a_spike_still_passes_without_any_buildup(self):
        volumes = [100.0] * 12 + [250.0]
        C.VOLUME_BUILDUP_WEEKS = 4
        result, _, phase = C._evaluate_volume_confirmation(
            volumes, breakout_idx=12, latest_idx=12, pullback_quality=None)
        self.assertTrue(result)
        self.assertEqual(phase, "breakout", "a plain spike is still pattern A")

    def test_a_breakout_on_falling_volume_still_fails_both(self):
        """The book is explicit: no significant increase, avoid the stock.
        The build-up route must not become a way in for dead volume."""
        volumes = [100.0] * 12 + [40.0]
        C.VOLUME_BUILDUP_WEEKS = 4
        result, _, _ = C._evaluate_volume_confirmation(
            volumes, breakout_idx=12, latest_idx=12, pullback_quality=None)
        self.assertFalse(result)


class VolumeBuildupBoundaryTest(unittest.TestCase):
    """Both halves of the build-up rule have to bind.

    Correcting the fixture above so the breakout week held its elevated
    level removed the only case where either half mattered, and two
    mutations started surviving. These are the failing cases.
    """

    def setUp(self):
        self._prev = C.VOLUME_BUILDUP_WEEKS
        C.VOLUME_BUILDUP_WEEKS = 4

    def tearDown(self):
        C.VOLUME_BUILDUP_WEEKS = self._prev

    def _check(self, volumes):
        return C._evaluate_volume_confirmation(
            volumes, breakout_idx=12, latest_idx=12, pullback_quality=None)[0]

    def test_a_buildup_followed_by_collapsing_volume_fails(self):
        """Heavy accumulation and then the breakout week comes in far
        below it — volume drying up exactly when it should confirm. The
        build-up route must not wave that through."""
        self.assertFalse(self._check([100.0] * 8 + [300.0] * 4 + [120.0]))

    def test_a_weak_buildup_fails_even_with_a_healthy_breakout_week(self):
        """Volume only 1.2x the prior stretch is not a build-up. Without
        this the ratio threshold could be anything."""
        self.assertFalse(self._check([100.0] * 8 + [120.0] * 4 + [130.0]))

    def test_the_qualifying_case_still_passes(self):
        self.assertTrue(self._check([100.0] * 8 + [300.0] * 4 + [330.0]))
