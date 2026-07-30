"""Short-side regressions, concentrated on the asymmetries.

The mirrored conditions are the easy part. What makes this module worth
having is the places the book says the two sides differ, and those are
exactly what a mechanical inversion of the long checklist would get
wrong. Every test here is about one of them.
"""
import unittest

from screener import conditions as C
from screener import short_conditions as S
from tests.synthetic import bar, weekly_dates


def _bars(closes, volumes=None):
    dates = weekly_dates(len(closes))
    vols = volumes or [1_000_000.0] * len(closes)
    return [bar(d, c * 1.02, c * 0.98, c, volume=v)
            for d, c, v in zip(dates, closes, vols)]


def _declining(n=120, start=200.0, rate=0.02):
    out, price = [], start
    for _ in range(n):
        out.append(price)
        price *= (1 - rate)
    return out


class VolumeAsymmetryTest(unittest.TestCase):
    """The asymmetry most likely to be lost by inverting the long rules.

    An upside breakout needs a significant volume increase to be
    trustworthy. A downside breakdown does not need one to be valid — the
    book warns explicitly against reading light volume as safety. Heavy
    volume is preferable for a short, since urgent selling falls faster,
    so it is recorded as a bonus and never as a gate.
    """

    def test_volume_is_not_one_of_the_conditions(self):
        self.assertNotIn("volume_confirmation", S.CONDITION_NAMES)
        self.assertFalse([n for n in S.CONDITION_NAMES if "volume" in n],
                         "no short condition may gate on volume")

    def test_a_light_volume_breakdown_is_still_valid(self):
        closes = _declining()
        light = _bars(closes, volumes=[500_000.0] * len(closes))
        result = S.evaluate_short_conditions("T", light, light)
        self.assertIsNot(result["conditions"]["support_breakdown"], False,
                         "light volume must not invalidate a breakdown")

    def test_heavy_breakdown_volume_is_reported_as_a_bonus(self):
        closes = _declining()
        vols = [1_000_000.0] * len(closes)
        result = S.evaluate_short_conditions("T", _bars(closes, vols), _bars(closes, vols))
        self.assertIn("heavy_breakdown", result)
        self.assertIn("breakdown_volume_ratio", result)

    def test_volume_never_blocks(self):
        self.assertNotIn("volume", " ".join(S.NON_NEGOTIABLE_CONDITIONS))


class NeverShortAnAdvanceTest(unittest.TestCase):
    """The book's hardest warning on the short side: never short on
    valuation, only on stage. Its worked example is a stock at 35 times
    earnings that doubled while the market fell."""

    def test_a_stage_2_stock_fails_the_setup_outright(self):
        rising, price = [], 100.0
        for _ in range(120):
            rising.append(price)
            price *= 1.02
        bars = _bars(rising)
        result = S.evaluate_short_conditions("T", bars, bars)
        self.assertEqual(result["stage"], 2)
        self.assertIs(result["conditions"]["stage_setup"], False)
        self.assertFalse(result["scoring"]["actionable"])

    def test_the_stage_setup_is_non_negotiable(self):
        self.assertIn("stage_setup", S.NON_NEGOTIABLE_CONDITIONS)

    def test_no_fundamental_input_exists_at_all(self):
        """There is no parameter through which valuation could enter.

        Asserted against the signature rather than by grepping the source
        — my first version searched the module text for "earnings" and
        tripped over its own docstring quoting the book. Testing what a
        function accepts is the contract; testing what words appear near
        it is not.
        """
        import inspect
        params = set(inspect.signature(S.evaluate_short_conditions).parameters)
        self.assertEqual(params, {"ticker", "bars", "index_bars", "sector_data"},
                         "a short decision takes price and index data, nothing else")


class RiskIsBoundedTest(unittest.TestCase):
    """A short at 40 with a buy-stop at 44 risks 10%, exactly as a long at
    40 with a sell-stop at 36 does. The same 15% ceiling applies."""

    def test_the_stop_ceiling_matches_the_long_side(self):
        self.assertEqual(S.MAX_SENSIBLE_STOP_PCT, C.MAX_SENSIBLE_STOP_PCT)

    def test_a_protective_stop_is_always_above_the_entry(self):
        closes = _declining()
        bars = _bars(closes)
        r = S.evaluate_short_conditions("T", bars, bars)
        if r["buy_stop"] is not None and r["price"] is not None:
            self.assertGreater(r["buy_stop"], r["price"],
                               "a short's protective stop sits above the entry")


class ShapeMatchesTheLongSideTest(unittest.TestCase):
    """Callers and reports treat both sides alike, so the result shape
    has to match — including for the empty case."""

    def test_empty_history_returns_key_parity(self):
        real = S.evaluate_short_conditions("T", _bars(_declining()), _bars(_declining()))
        self.assertEqual(set(real), set(S._empty_result()))

    def test_empty_history_is_not_actionable(self):
        self.assertFalse(S.evaluate_short_conditions("T", [], [])["scoring"]["actionable"])

    def test_scoring_reports_the_same_fields_as_the_long_side(self):
        short = S.score_short_conditions({n: True for n in S.CONDITION_NAMES})
        long_ = C.score_conditions({n: True for n in C.CONDITION_NAMES})
        self.assertEqual(set(short) - {"extension_above_ma_pct", "too_extended"},
                         set(long_) - {"extension_above_ma_pct", "too_extended"})
